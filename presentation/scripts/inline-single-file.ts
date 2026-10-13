import type { Plugin } from "vite";

/**
 * Inlines the JavaScript and CSS that `vite build` emits into `index.html`, so
 * `dist/index.html` is one self-contained file that opens from disk. Local
 * replacement for `vite-plugin-singlefile`, which pulls a vulnerable
 * `micromatch`/`braces` into the dependency tree.
 */
export function inlineSingleFile(): Plugin {
  return {
    name: "inline-single-file",
    enforce: "post",
    generateBundle(_options, bundle) {
      const html = bundle["index.html"];
      if (!html || html.type !== "asset") {
        this.error("index.html was not emitted; nothing to inline into");
      }
      let source = String(html.source);
      const scripts = /<script\b[^>]*\bsrc="([^"]+)"[^>]*><\/script>/g;
      const links =
        /<link\b[^>]*\brel="stylesheet"[^>]*\bhref="([^"]+)"[^>]*>/g;
      const lookup = (ref: string) => {
        const name = ref.replace(/^\.\//, "").replace(/^\//, "");
        const file = bundle[name];
        if (!file) this.error(`cannot inline "${ref}": not in the bundle`);
        delete bundle[name];
        return file;
      };
      source = source.replace(scripts, (tag, ref: string) => {
        const file = lookup(ref);
        if (file.type !== "chunk") this.error(`"${ref}" is not a script chunk`);
        const type = /\btype="module"/.test(tag) ? ' type="module"' : "";
        // `<\/script` keeps a literal end tag in the code from closing the block.
        const code = file.code.replace(/<(\/script)/gi, "<\\$1");
        return `<script${type} crossorigin>${code}</script>`;
      });
      source = source.replace(links, (_tag, ref: string) => {
        const file = lookup(ref);
        if (file.type !== "asset") this.error(`"${ref}" is not a stylesheet`);
        const css = String(file.source).replace(/<(\/style)/gi, "<\\$1");
        return `<style rel="stylesheet" crossorigin>${css}</style>`;
      });
      html.source = source;
    },
  };
}
