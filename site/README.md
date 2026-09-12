# Loop showcase

A single-page React + Vite showcase for Loop, with an interactive workflow overview, assignment-folder guide, and setup links.

Requires Node.js 22.12+.

```sh
cd site
npm ci
npm run dev
```

`npm run build` produces `site/dist/`. `npm run preview` serves that production build locally. Deploy the contents of `dist/` to a static host; relative asset paths support subdirectory hosting, including GitHub Pages. Do not serve the source `index.html` directly.

The page follows the system color preference initially and remembers manual theme changes. Workflow tabs support arrow keys, Home, and End. Fonts are bundled locally; the page does not require a backend or third-party font requests.
