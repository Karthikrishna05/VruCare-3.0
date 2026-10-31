from django.contrib import admin

from .models import EvalJudgement, EvalQuestion, EvalRun

admin.site.register([EvalJudgement, EvalQuestion, EvalRun])
