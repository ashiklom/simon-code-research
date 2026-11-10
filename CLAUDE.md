Each code experiment lives in its own subdirectory with a short but informative name (create automatically if not provided explicitly).

In each experiment's subdirectory:
    - README.md --- GitHub flavored markdown; describes the experiment and, briefly, its results, with a link to the corresponding page on GitHub Pages.
    - PROMPT.md --- My original prompt. Any additional clarifying messages I send, answers to your questions, etc. should be appended to this.
    - PLAN.md --- If I use Claude plan mode, the accepted plan.
    - Each experiment should manage as many of its own dependencies as reasonable (with lockfiles), using a combination of tools including (but not limited to) uv, mise, pixi, rig (for R), and Nix.

Each experiment should also get a short description and a link to its directory in the repository root README.md.

GitHub pages are configured for deployment via GitHub Actions. There should be a single homepage that links to the experiments with a summary (similar to /README.md). Each experiment also gets its own website in a sub-path (matching the folder name); experiments can optionally have sub-pages, interactive web content (Javascript/Typescript), etc. Experiment web pages with large assets can bundle large assets as GitHub releases with a name that matches the experiment folder name, which are pulled by GitHub Actions during the website build.
