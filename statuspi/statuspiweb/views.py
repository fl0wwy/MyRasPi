from django.shortcuts import render
from .metrics import get_metrics
from django.http import JsonResponse
from django.shortcuts import render
import json, time


# Create your views here.
def index(request):
    context = get_metrics()
    return render(request, "statuspiweb/index.html", context=context)

def metrics(request):
    return JsonResponse(get_metrics())
