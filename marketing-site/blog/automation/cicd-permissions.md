# CI/CD and Permission Separation Design

## Current stack inspected
The marketing site is static HTML/CSS/JS. The safest compatible implementation is a static generator committed to the repo, with generated HTML committed when required by the host.

## Preferred pipeline
1. Hermes creates source changes in `marketing-site/blog/content/` and automation config.
2. `python3 marketing-site/blog/scripts/generate_blog.py` renders deterministic static output.
3. `python3 marketing-site/blog/tests/test_blog_system.py` verifies generated-file drift, metadata, draft state, sitemap exclusion, schema, layout regression artifacts, and policy defaults.
4. Marketing OS preflight validates article drafts.
5. Preview artifact or branch preview is produced.
6. Shadow-mode publish dry run runs through `marketing-site/blog/scripts/hermes_blog.py publish <article-id> --dry-run`.
7. Scheduled production publication, once activated, must use `hermes_blog.py publish <article-id> --scheduled` only.
8. Live QA runs through `hermes_blog.py verify-live <article-id>` once a live URL exists.
9. Rollback uses `hermes_blog.py rollback <article-id>` or deployment rollback.

## Credential separation
- Research permissions: SERP/Search Console read-only when connected.
- Source-editing permissions: Git branch/worktree only.
- Preview deployment permissions: branch preview only.
- Production publication permissions: controlled wrapper only.
- Rollback permissions: deployment rollback only.

The content-writing process must not receive unrestricted production deploy credentials that bypass the publish wrapper.

## Branch protections recommended
- Require tests before merge.
- Require review for `publication-policy.json`, deployment config, and production sitemap changes.
- Require explicit activation flag for autopublish.
- Block direct pushes to production branch by autonomous content jobs.
