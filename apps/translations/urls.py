from django.urls import path
from translations import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('tasks/upload', views.upload_task_view, name='upload_task'),
    path('tasks/upload/', views.upload_task_view, name='upload_task_slash'),
    path('tasks/<str:task_id>/status/', views.task_status_view, name='task_status'),
    path('tasks/<str:task_id>/download/', views.task_download_view, name='task_download'),
    path('tasks/<str:task_id>/delete/', views.task_delete_view, name='task_delete'),
    path('tasks/delete-all/', views.task_delete_all_view, name='task_delete_all'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('payment/checkout/', views.payment_checkout_view, name='payment_checkout'),
    path('payment/process/', views.payment_process_view, name='payment_process'),
    
    # Custom Admin Panel
    path('admin-panel/', views.admin_panel_view, name='admin_panel'),
    path('admin-panel/providers/create/', views.admin_create_provider_view, name='admin_create_provider'),
    path('admin-panel/providers/<int:provider_id>/delete/', views.admin_delete_provider_view, name='admin_delete_provider'),
    path('admin-panel/providers/<int:provider_id>/toggle/', views.admin_toggle_provider_view, name='admin_toggle_provider'),
    path('admin-panel/providers/<int:provider_id>/test/', views.admin_test_provider_view, name='admin_test_provider'),
    path('admin-panel/providers/reorder/', views.admin_reorder_providers_view, name='admin_reorder_providers'),
    path('admin-panel/users/<int:user_id>/update/', views.admin_update_user_view, name='admin_update_user'),
    # API Routes
    path('api/providers/add/', views.api_create_provider_view, name='api_create_provider'),
]

