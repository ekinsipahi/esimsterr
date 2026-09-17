import json

from django.conf import settings
from django.shortcuts import get_object_or_404, render

from apps.common import schema

from .models import Post


def index(request):
    return render(request, "blog/index.html", {
        "posts": Post.objects.filter(is_published=True),
        "seo_title": f"Travel guides & eSIM tips | {settings.SITE_NAME}",
        "seo_description": "Practical guides on staying connected abroad: eSIM setup, data costs, "
                           "coverage and country-by-country advice.",
    })


def detail(request, slug):
    post = get_object_or_404(Post, slug=slug, is_published=True)
    # Publisher and author point at the organisation node the rest of the site
    # describes, rather than repeating a bare name: that is what tells a crawler
    # the company selling the plans and the one writing the guides are the same.
    return render(request, "blog/detail.html", {
        "post": post,
        "related": Post.objects.filter(is_published=True).exclude(pk=post.pk)[:3],
        "article_jsonld": schema.dumps(schema.article(request, post)),
        "seo_title": post.seo_title or f"{post.title} | {settings.SITE_NAME}",
        "seo_description": post.seo_description or post.excerpt[:300],
        "breadcrumbs": [("Home", "/"), ("Blog", "/blog/"), (post.title, None)],
    })
