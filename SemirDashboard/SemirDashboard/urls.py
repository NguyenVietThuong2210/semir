from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('App.urls')),  # Existing web views
    path('cnv/', include('App.cnv.urls')),
    path('api/v1/', include('App.api.urls')),  # SemirPhone JSON API (Sprint 0)
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)