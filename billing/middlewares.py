import os
from subscriptions.endpoints import sub_authorized_endpoints
from games.endpoints import games_authorized_endpoints
from billing.endpoints import billing_authorized_endpoints

from django.http import JsonResponse, HttpResponse
from rest_framework.exceptions import ValidationError

from django.urls import resolve



class AuthorizedMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        all_authorized_urls = games_authorized_endpoints + sub_authorized_endpoints + billing_authorized_endpoints
        normalized_urls = [str(item.name) for item in all_authorized_urls]
        resolve_match = resolve(request.path)
        view_name = resolve_match.url_name

        PATH_PREFIXES = {
            "api_path": [
                '/api/subscription-services/',
                '/api/console-types/',
                '/api/subscriptions/',
            ],
            "excluded_paths": [
                '/swagger',
                '/redoc',
                '/swagger.json'
            ]
        }
        if any(request.path.startswith(prefix) for prefix in PATH_PREFIXES["excluded_paths"]):
            return self.get_response(request)

        if view_name in normalized_urls or any(request.path.startswith(prefix) for prefix in PATH_PREFIXES["api_path"]):
            authorization_header = request.headers.get('Authorization')

            if authorization_header:
                try:
                    token = os.getenv('TOKEN')
                    if not authorization_header or token not in authorization_header:
                        return JsonResponse({"detail": "Unauthorized request"}, status=401)

                except ValidationError:
                    return JsonResponse({"detail": "Unauthorized request"}, status=401)
            else:
                return JsonResponse({"detail": "Unauthorized request"}, status=401)
        referer = request.headers.get('Referer', '')
        # if referer and not referer.startswith('localhost:8000/'):
        #     return JsonResponse({"detail": "Access denied"}, status=403)

        response = self.get_response(request)
        return response


# class CountLimitingMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         print(self.get_client_ip(request))

#         all_authorized_urls = games_authorized_endpoints + sub_authorized_endpoints + billing_authorized_endpoints
#         normalized_urls = [str(item.name) for item in all_authorized_urls]
#         resolve_match = resolve(request.path)
#         view_name = resolve_match.url_name

#         if view_name in normalized_urls:
#             ip = self.get_client_ip(request)
#             redis_key = f"request_count:{ip}"

#             if redis_instance.exists(redis_key):
#                 total_count = int(redis_instance.get(redis_key))
#                 if total_count >= 20:
#                     return JsonResponse({"message": "Please wait 5 minutes and try again"}, status=429)
#                 else:
#                     redis_instance.incr(redis_key)
#             else:
#                 redis_instance.set(redis_key, 1, ex=300)
#         response = self.get_response(request)
#         return response

#     def get_client_ip(self, request):
#         x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
#         if x_forwarded_for:
#             return x_forwarded_for.split(',')[0]
#         return request.META.get('REMOTE_ADDR')