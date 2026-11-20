from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from careercoach.security import rate_limited, serialized_user_work
from .constants import ERRORS
from .forms import ResumeUploadForm
from .models import ResumeDocument
from .services.documents import ResumeRejected, accept_document, delete_document
from .storage import ResumeStorageError, private_storage


def private_response(response):
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    response.setdefault('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
    return response


@login_required
@require_GET
@never_cache
def index(request):
    from django.core.paginator import Paginator
    page = Paginator(ResumeDocument.objects.filter(owner=request.user).defer('extracted_text'), 10).get_page(request.GET.get('page'))
    return private_response(render(request, 'resume/list.html', {'page': page}))


@transaction.non_atomic_requests
@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
@sensitive_post_parameters()
@sensitive_variables()
@rate_limited('resume-upload', 'RESUME_UPLOADS_PER_DAY', 86400, by_user=True)
@serialized_user_work
def upload(request):
    form = ResumeUploadForm(request.POST, request.FILES) if request.method == 'POST' else ResumeUploadForm()
    status = 200
    if request.method == 'POST':
        status = 400
        if getattr(request, 'resume_upload_too_large', False):
            form.add_error(None, ERRORS['file_too_large'])
            status = 413
        elif form.is_valid():
            if ResumeDocument.objects.filter(owner=request.user).count() >= settings.RESUME_MAX_DOCUMENTS:
                form.add_error(None, f'Delete an existing resume before uploading another (maximum {settings.RESUME_MAX_DOCUMENTS}).')
            else:
                try:
                    document = accept_document(request.user, form.cleaned_data['document'])
                    return private_response(redirect('resume:detail', pk=document.pk))
                except ResumeRejected as exc:
                    form.add_error(None, ERRORS.get(exc.code, ERRORS['extraction_failed']))
                    status = 503 if exc.code in ('worker_unavailable', 'storage_unavailable') else 400
                except Exception:
                    form.add_error(None, 'Resume processing is temporarily unavailable. Please try again later.')
                    status = 503
    return private_response(render(request, 'resume/upload.html', {'form': form}, status=status))


@login_required
@require_GET
@never_cache
def detail(request, pk):
    document = get_object_or_404(ResumeDocument, pk=pk, owner=request.user)
    return private_response(render(request, 'resume/detail.html', {'document': document, 'error_message': ERRORS.get(document.error_code, '')}))


@login_required
@require_GET
@never_cache
def confirm_delete(request, pk):
    document = get_object_or_404(ResumeDocument.objects.defer('extracted_text'), pk=pk, owner=request.user)
    return private_response(render(request, 'resume/confirm_delete.html', {'document': document}))


@login_required
@require_POST
@never_cache
@serialized_user_work
def delete(request, pk):
    document = get_object_or_404(ResumeDocument.objects.defer('extracted_text'), pk=pk, owner=request.user)
    try:
        delete_document(document)
    except (ResumeStorageError, DatabaseError):
        return private_response(render(request, 'resume/error.html', {'message': 'Deletion could not finish. Your record remains private; please try again.'}, status=503))
    return private_response(redirect('resume:index'))


@login_required
@require_GET
@never_cache
def download(request, pk):
    document = get_object_or_404(ResumeDocument.objects.defer('extracted_text'), pk=pk, owner=request.user, file_retained=True,
        status__in=[ResumeDocument.Status.COMPLETED, ResumeDocument.Status.NO_TEXT])
    try:
        stream = private_storage().open(document.storage_key, 'rb')
    except Exception:
        raise Http404('Document unavailable') from None
    response = FileResponse(stream, as_attachment=True, filename=f'resume.{document.file_type}', content_type='application/octet-stream')
    response['Content-Security-Policy'] = "sandbox; default-src 'none'"
    response['X-Frame-Options'] = 'DENY'
    return private_response(response)
