# md4a

`md4a` installs [md4a-fastapi](https://pypi.org/project/md4a-fastapi/), Markdown for
Agents content negotiation for FastAPI, Flask, and other WSGI applications. It adds
no code of its own; both distributions provide the same `md4a` import package and
are released together at the same version.

```bash
python -m pip install md4a            # same as md4a-fastapi
python -m pip install 'md4a[server]'  # same as md4a-fastapi[server]
```

```python
from md4a import add_md4a, MarkdownForAgentsWSGIMiddleware
```

Documentation, changelog, and issues:
https://github.com/adamtasteslikegood/md4a-fastapi
