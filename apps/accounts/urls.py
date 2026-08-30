from django.urls import path
from accounts import views

urlpatterns = [
    path('login/', views.login_view, name='auth_login'),
    path('logout/', views.logout_view, name='auth_logout'),
    path('send-otp/', views.send_otp_view, name='send_otp'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
]
