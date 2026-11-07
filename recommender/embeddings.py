from django.conf import settings

_model = None
MODEL_NAME = "all-MiniLM-L6-v2"


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(
            settings.EMBEDDING_MODEL_PATH,
            local_files_only=settings.EMBEDDING_LOCAL_FILES_ONLY,
        )
    return _model
