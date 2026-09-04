from django.urls import path

from apps.projects import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/", views.project_create, name="create"),
    path("<int:project_id>/", views.project_detail, name="detail"),
    path("<int:project_id>/quick/", views.project_quickview, name="quickview"),
    path("<int:project_id>/edit/", views.project_edit, name="edit"),
    path("<int:project_id>/archive/", views.project_archive, name="archive"),
    path("<int:project_id>/asins/", views.project_asins, name="asins"),
    path("<int:project_id>/keywords/", views.project_keywords, name="keywords"),
    path("<int:project_id>/ranks/", views.project_ranks, name="ranks"),
    path("<int:project_id>/trends/", views.project_trends, name="trends"),
    path("<int:project_id>/keyword/<path:keyword>/", views.keyword_detail, name="keyword_detail"),
]
