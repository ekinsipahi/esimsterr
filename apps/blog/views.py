import json

from django.conf import settings
from django.shortcuts import get_object_or_404, render

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
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post.title,
        "description": post.excerpt,
        "datePublished": post.published_at.isoformat(),
        "dateModified": post.updated_at.isoformat(),
        "author": {"@type": "Organization", "name": settings.SITE_NAME},
        "publisher": {"@type": "Organization", "name": settings.SITE_NAME},
    }
    return render(request, "blog/detail.html", {
        "post": post,
        "related": Post.objects.filter(is_published=True).exclude(pk=post.pk)[:3],
        "article_jsonld": json.dumps(article, ensure_ascii=False),
        "seo_title": post.seo_title or f"{post.title} | {settings.SITE_NAME}",
        "seo_description": post.seo_description or post.excerpt[:300],
        "breadcrumbs": [("Home", "/"), ("Blog", "/blog/"), (post.title, None)],
    })
