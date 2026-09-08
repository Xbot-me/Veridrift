from __future__ import annotations

from guardrail.models.run import VerificationRun
from guardrail.reporting.markdown_reporter import MarkdownReporter


class HTMLReporter:
    """Reporter that generates an HTML report wrapping the Markdown output."""

    def render(self, run: VerificationRun) -> str:
        """
        Render the verification run to an HTML string.

        Args:
            run: The completed verification run data.

        Returns:
            A string containing HTML.
        """
        md_content = MarkdownReporter().render(run)

        # Note: In a full implementation, we'd use a Markdown-to-HTML parser like `markdown`
        # and Jinja2 for templating. For now, we stub the HTML structure.

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Guardrail Verification Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1000px;
            margin: 0 auto;
            padding: 2rem;
            background-color: #f9f9f9;
        }}
        @media (prefers-color-scheme: dark) {{
            body {{
                background-color: #1e1e1e;
                color: #e0e0e0;
            }}
            .container {{ background-color: #2d2d2d; }}
        }}
        .container {{
            background-color: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        pre {{ background-color: #f4f4f4; padding: 1rem; border-radius: 4px; overflow-x: auto; }}
        @media (prefers-color-scheme: dark) {{
            pre {{ background-color: #3d3d3d; }}
        }}
    </style>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true }});
    </script>
</head>
<body>
    <div class="container">
        <!-- Markdown content will be rendered here by a JS library or backend parser -->
        <pre>{md_content}</pre>
    </div>
</body>
</html>"""

        return html_template
