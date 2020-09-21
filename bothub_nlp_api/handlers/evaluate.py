from bothub_nlp_celery.actions import ACTION_EVALUATE, queue_name
from bothub_nlp_celery.app import celery_app
from bothub_nlp_celery.tasks import TASK_NLU_EVALUATE_UPDATE
from bothub_nlp_celery.utils import ALGORITHM_TO_LANGUAGE_MODEL, choose_best_algorithm, get_language_model
from bothub_nlp_celery import settings as celery_settings

from .. import settings
from ..utils import AuthorizationIsRequired
from ..utils import NEXT_LANGS
from ..utils import ValidationError, get_repository_authorization
from ..utils import backend

EVALUATE_STATUS_EVALUATED = "evaluated"
EVALUATE_STATUS_FAILED = "failed"


def evaluate_handler(authorization, language, repository_version=None, cross_validation=False):
    if language and (
        language not in settings.SUPPORTED_LANGUAGES.keys()
        and language not in NEXT_LANGS.keys()
    ):
        raise ValidationError("Language '{}' not supported by now.".format(language))

    repository_authorization = get_repository_authorization(authorization)
    if not repository_authorization:
        raise AuthorizationIsRequired()

    try:
        update = backend().request_backend_evaluate(
            repository_authorization, language, repository_version
        )
    except Exception:
        update = {}

    if not update.get("update"):
        raise ValidationError("This repository has never been trained")

    model = get_language_model(update, language)

    try:
        evaluate_task = celery_app.send_task(
            TASK_NLU_EVALUATE_UPDATE,
            args=[
                update.get("repository_version"),
                update.get("user_id"),
                repository_authorization,
                cross_validation,
            ],
            queue=queue_name(update.get("language"), ACTION_EVALUATE, model),
        )
        evaluate_task.wait()
        evaluate = evaluate_task.result
        evaluate_report = {
            "language": language,
            "status": EVALUATE_STATUS_EVALUATED,
            "repository_version": update.get("repository_version"),
            "evaluate_id": evaluate.get("id"),
            "evaluate_version": evaluate.get("version"),
            "cross_validation": cross_validation,
        }
    except Exception as e:
        evaluate_report = {"status": EVALUATE_STATUS_FAILED, "error": str(e)}

    return evaluate_report
