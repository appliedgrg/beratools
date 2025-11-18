# Documentation

BERA Tools uses MkDocs for user/developer/API documentation. MkDocs is a static site generator that's geared towards project documentation. The documentation source files are written in Markdown and are located in the `docs/` folder of the GitHub repository.

## Documentation File Structure

```bash
docs/
├── files/                  # Main documentation folder
│   ├── api.md              # API reference
│   ├── developer_guide.md  # Developer guide
│   ├── index.md            # Documentation homepage
│   ├── overview.md         # Project overview
│   ├── requirements.txt    # Python requirements for mkdocs
│   ├── user_guide.md       # User guide
│   │
│   ├── css/                # Custom CSS for docs
│   ├── developer/          # Developer-specific docs
│   ├── icons/              # Project and documentation icons
│   ├── screenshots/        # Screenshots for guides and docs
│   ├── user/               # User-specific documentation
├── mkdocs.yml              # MkDocs configuration file
```

## Contribution Guidelines

To contribute to the documentation, please follow these guidelines:

1. **Clarity**: Write clear and concise documentation.
2. **Structure**: Organize content logically. Use headings, subheadings, and bullet points for easy navigation.
3. **Examples**: Provide examples to illustrate complex concepts. Code snippets should be tested and functional.
4. **Updates**: Keep documentation up-to-date with the latest changes in the codebase.
5. **Review Process**: All documentation changes should be submitted as pull requests like code changes.

By following these guidelines, you can help ensure that BERA Tools documentation remains a valuable resource for all users.

## Developing Documentation Locally

To build the documentation locally, you need to have MkDocs and extensions installed in development environment.

1. Install the required dependencies in development environment using the `docs/requirements.txt` file:

   ```bash
   pip install -r requirements.txt
   ```

   or use the pyproject.toml in the root directory:

   ```bash
   pip install .[doc]
   ```

2. Serve the live documentation locally
   This command starts a local development server that automatically rebuilds the documentation when changes are made . It is useful for previewing changes in real-time.

   ```bash
   mkdocs serve
   ```

 Open your browser and navigate to `http://127.0.0.1:8000` to view the documentation.

1. Build the documentation locally
This generates the static site files in the `site/` directory. It's optional for local preview (use `mkdocs serve` for a live‑reloading preview).

```bash
mkdocs build
```

## Deployment

The documentation is automatically deployed to GitHub Pages using a GitHub Actions workflow defined in `.github/workflows/mkdocs-gh-pages.yml`.

This workflow triggers on pushes to the `main` branch that affect files in the `docs/` directory. It builds the documentation and publishes it to the `gh-pages` branch, making it available at `https://appliedgrg.github.io/beratools/`.

![Doc Deployment Config](../screenshots/gh_pages_config.png)