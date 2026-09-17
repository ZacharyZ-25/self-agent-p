import { mkdir, copyFile } from "node:fs/promises";
const root = new URL("../", import.meta.url);
await mkdir(new URL("dist/", root), { recursive: true });
for (const name of ["index.html", "chat-widget.js", "style-demo.html"])
  await copyFile(new URL(name, root), new URL(`dist/${name}`, root));
console.log("Built static frontend in frontend/dist");
