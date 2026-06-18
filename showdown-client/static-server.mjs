import {createServer} from "node:http";
import {extname, join, normalize} from "node:path";
import {readFile} from "node:fs/promises";

const root = "/opt/client/play.pokemonshowdown.com";
const contentTypes = {
  ".css": "text/css",
  ".html": "text/html",
  ".ico": "image/x-icon",
  ".js": "application/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

createServer(async (request, response) => {
  let pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname);
  if (pathname === "/" || pathname === "") {
    pathname = "/index-new.html";
  }

  const filePath = normalize(join(root, pathname));
  if (!filePath.startsWith(root)) {
    response.writeHead(403);
    response.end("forbidden");
    return;
  }

  try {
    const data = await readFile(filePath);
    response.writeHead(200, {"content-type": contentTypes[extname(filePath)] ?? "application/octet-stream"});
    response.end(data);
  } catch {
    response.writeHead(404);
    response.end("not found");
  }
}).listen(8000, "0.0.0.0");
