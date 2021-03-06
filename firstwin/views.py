from celery.result import AsyncResult
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.http import HttpResponse
from django.shortcuts import render, redirect

from firstwin.tasks import wrapper_defects_processing, wrapper_default_defects_processing
from firstwin.utils import *
from .forms import CodeInsertForm, ChooseMeSenpai


def index_view(request):
    if request.method == "POST":
        form_class = CodeInsertForm(request.POST)

        if form_class.is_valid():
            source_code = form_class.cleaned_data["content"]

            task = wrapper_default_defects_processing.delay(source_code)

            if task:
                request.session['task_id'] = task.task_id
                return redirect('/result/')
            else:
                return HttpResponse('Borealis can\'t find any mistakes!')
    else:
        form_class = CodeInsertForm
        return render(request, 'index.html', {
            'form': form_class,
        })


@login_required
def repository_check_view(request):
    # tuple of all (public) user repositories
    user_repos_tuple = tuple

    user_object = request.user

    if request.session['social_auth_last_login_backend']:
        user_auth_backend = request.session['social_auth_last_login_backend']
    else:
        return HttpResponse('Can\'t detect your authentication backend')

    if user_auth_backend == 'bitbucket':
        user_repos_tuple = get_bitbucket_repos_tuple(user_object.username)

    if user_auth_backend == 'github':
        user_repos_tuple = get_github_repos_tuple(user_object.username)

    if request.method == 'POST':
        choice = ChooseMeSenpai(request.POST, repos_choices=user_repos_tuple)

        if choice.is_valid():
            user_repos_choice = choice.cleaned_data['choices']

            if wrapper_defects_processing.delay(user_object.pk, user_auth_backend, user_repos_choice):
                return HttpResponse('Thank you for using Borealis! '
                                    'It\'s can take a while to check whole project, so '
                                    'we will inform you via email when it\'s ready.')
            else:
                return HttpResponse('Selected repository doesn\'t contain makefile!')
    else:
        choices = ChooseMeSenpai(repos_choices=user_repos_tuple)

        return render(request, 'repocheck.html', {
            'choices': choices,
        })


@login_required
def history_view(request):
    user_searches = get_defect_search_queryset('-time', user=request.user)

    history_paginator = Paginator(user_searches, 50)

    history_page = request.GET.get('page')
    try:
        history = history_paginator.page(history_page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        history = history_paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        history = history_paginator.page(history_paginator.num_pages)

    return render(request, 'history.html', {
        'history': history,
    })


@login_required
def search_detail_view(request, repository, time):
    search = get_defect_search_queryset(user=request.user, repository=repository,
                                        time='%s-%s-%s %s:%s:%s' % tuple(time.split('-')))

    defects_query = get_defect_queryset('file_name', 'line', defect_search=search)

    defected_files_query = defects_query.order_by('file_name').values('file_name').distinct()

    files_query = []
    for file in defected_files_query:
        tmp_defects_query = defects_query.filter(file_name=file['file_name'])
        files_query.append({'file_name': file['file_name'],
                            'defects_amount': tmp_defects_query.count(),
                            'link': tmp_defects_query[0].get_absolute_url()})

    search_history_paginator = Paginator(files_query, 50)

    search_history_page = request.GET.get('page')
    try:
        search_history = search_history_paginator.page(search_history_page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        search_history = search_history_paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        search_history = search_history_paginator.page(search_history_paginator.num_pages)

    return render(request, 'search_detail.html', {
        'search_history': search_history,
    })


@login_required
def show_defects_view(request, repository, time, file_name):
    styled_code_list = mark_defects_in_file(request.user, repository, time, file_name)

    if styled_code_list:
        marked_code = '\n'.join(styled_code_list)
        return render(request, 'result.html', {
            'marked_code': marked_code,
        })
    else:
        return HttpResponse('Can\'t find selected file.')


def logout_view(request):
    logout(request)
    return redirect('/')


def result_view(request):
    if request.is_ajax():
        result = AsyncResult(request.session['task_id'])

        if result.ready():
            ret = {'status': 'solved'}
            ret.update({'code': str('\n'.join(result.get()))})
        else:
            ret = {'status': 'waiting'}

        return HttpResponse(json.dumps(ret))

    return render(request, 'result.html')
