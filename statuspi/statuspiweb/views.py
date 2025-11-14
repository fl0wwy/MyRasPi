from django.shortcuts import render
from .metrics import load_metrics
from django.http import JsonResponse
from django.shortcuts import render
import json, time


# Create your views here.
def index(request):
    context = load_metrics(0)
    return render(request, "statuspiweb/index.html", context=context)

def metrics(request):
    refresh_rate_ms = int(request.GET.get("refresh_rate", 0))
    return JsonResponse(load_metrics(refresh_rate_ms))
