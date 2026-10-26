# سبق (Sabaq)

خطة تدريب بالعربي لحد يوم السباق: جري و HYROX، في مصر وبعدين الخليج.

## الفولدر ده فيه إيه

| المكان | فيه إيه |
| --- | --- |
| `CLAUDE.md` | كل اللي Claude Code لازم يعرفه: القرارات، والتقنيات، والقواعد اللي ممنوع يكسرها |
| `FIRST_PROMPT.md` | أول رسالة تبعتها لـ Claude Code |
| `docs/product.md` | الصفحات، والفلو، والحالات الصعبة (عيّان، وجع، فوّت أيام) |
| `docs/engine-rules.md` | قواعد محرّك الخطط بالتفصيل، للمراجعة مع كوتش |
| `docs/architecture.md` | إزاي المشروع متقسّم عشان يكبر ويتعدّل بسهولة |
| `docs/security.md` | الأمان وحماية البيانات الصحية والدفع |
| `docs/brand.md` | الألوان، والخطوط، واللوجو، وطريقة الكلام |
| `docs/roadmap.md` | المراحل والمهام بالتواريخ، وحاجات لازم تعملها انت بنفسك |
| `reference/engine-js/` | المحرّك الشغال بالـ JavaScript، واختباراته، و21 حالة جاهزة يتقارن بيها المحرّك الجديد |
| `reference/plan-lab.html` | نسخة تجريبية تفتحها في المتصفح |
| `brand/` | اللوجوهات، وملفات الخطوط، والألوان |

## إزاي تبدأ

1. اعمل ريبو **Private** على GitHub وارفع الفولدر ده عليه.
2. افتحه في Claude Code.
3. ابعتله الرسالة اللي في `FIRST_PROMPT.md`.
4. ابدأ «حاجات لازم تعملها انت» اللي في أول `docs/roadmap.md` النهارده، لأنها بتاخد وقت (حساب Paymob، الدومين، الكوتش، المحامي).

## Run it (developers)

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                          # install pinned packages (uv.lock, with hashes)
uv run pre-commit install        # ruff, format and gitleaks on every commit
uv run python manage.py migrate  # SQLite locally unless POSTGRES_HOST is set
uv run python manage.py runserver
uv run pytest                    # all tests with coverage
```

Everything (web, worker, PostgreSQL, Redis, Caddy with HTTPS):

```bash
cp .env.example .env   # then replace every value
docker compose up --build
# https://localhost/  (Caddy's local certificate). The admin is at DJANGO_ADMIN_URL.
```

Quality gates (the same ones CI runs on every PR):

```bash
uv run pre-commit run --all-files
uv run mypy .
uv run pytest
uv run bandit -c pyproject.toml -r apps sabaq
uv run pip-audit --strict
DJANGO_SETTINGS_MODULE=sabaq.settings.prod uv run python manage.py check --deploy --fail-level WARNING
uv run python manage.py makemigrations --check --dry-run
```
