from django.contrib.auth import authenticate, get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
User=get_user_model()
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
 username=request.data.get('username','').strip(); password=request.data.get('password','')
 if len(username)<3 or len(password)<8:return Response({'error':'username_or_password_invalid'},status=400)
 if User.objects.filter(username=username).exists():return Response({'error':'username_exists'},status=409)
 user=User.objects.create_user(username=username,password=password); token=Token.objects.create(user=user); return Response({'token':token.key,'user_id':user.id},status=201)
@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
 user=authenticate(username=request.data.get('username',''),password=request.data.get('password',''))
 if not user:return Response({'error':'invalid_credentials'},status=401)
 token,_=Token.objects.get_or_create(user=user); return Response({'token':token.key,'user_id':user.id})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):return Response({'id':request.user.id,'username':request.user.username,'is_staff':request.user.is_staff})
