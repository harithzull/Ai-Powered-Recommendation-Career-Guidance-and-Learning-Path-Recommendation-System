"""Database-backed fixed-window limits and leases shared across workers."""
import logging
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.db import DatabaseError
from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac

from accounts.models import SecurityCounter

logger = logging.getLogger(__name__)


def _key(scope, identity):
    return salted_hmac("careercoach.security", f"{scope}:{identity}").hexdigest()


def consume(scope, identity, limit, seconds):
    """Reserve an attempt atomically. Fail closed if the counter store fails."""
    now = timezone.now()
    window = int(now.timestamp()) // seconds
    key = _key(scope, f"{identity}:{window}")
    try:
        SecurityCounter.objects.get_or_create(
            key=key, defaults={"expires_at": now + timedelta(seconds=seconds)},
        )
        return bool(SecurityCounter.objects.filter(key=key, count__lt=limit).update(count=F("count") + 1))
    except DatabaseError:
        logger.warning("Rate-limit store unavailable")
        return False


def rate_limited(scope, limit_setting, seconds, *, by_user=False):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST":
                # Do not trust attacker-controlled X-Forwarded-For headers.
                identity = request.user.pk if by_user else request.META.get("REMOTE_ADDR", "unknown")
                if not consume(scope, identity, getattr(settings, limit_setting), seconds):
                    response = JsonResponse({"error": "Too many requests. Please try again later."}, status=429)
                    response["Retry-After"] = str(seconds)
                    return response
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


class WorkInProgress(Exception):
    pass


@contextmanager
def user_work_lock(user):
    """Serialize assessment edits, cache writes, and AI work for each user.

    A crashed worker's lease expires. The expiry also acts as an ownership token
    so a slow worker cannot release a newer worker's lease.
    """
    key = _key("work", user.pk)
    now = timezone.now()
    token = now + timedelta(minutes=5)
    _, created = SecurityCounter.objects.get_or_create(
        key=key, defaults={"count": 1, "expires_at": token},
    )
    if not created and not SecurityCounter.objects.filter(key=key, expires_at__lte=now).update(
        count=1, expires_at=token,
    ):
        raise WorkInProgress
    try:
        yield
    finally:
        SecurityCounter.objects.filter(key=key, expires_at=token).delete()


def serialized_user_work(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.method != "POST":
            return view(request, *args, **kwargs)
        try:
            with user_work_lock(request.user):
                return view(request, *args, **kwargs)
        except WorkInProgress:
            return JsonResponse({"error": "Another request is being processed. Please try again."}, status=409)
    return wrapped
