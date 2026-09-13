export class JsonBodyTooLargeError extends Error {
  constructor(readonly maxBytes: number) {
    super(`Request body exceeds ${maxBytes} bytes.`);
    this.name = "JsonBodyTooLargeError";
  }
}

export class InvalidJsonBodyError extends Error {
  constructor() {
    super("Request body is not valid JSON.");
    this.name = "InvalidJsonBodyError";
  }
}

/**
 * Read and parse JSON without ever accumulating more than maxBytes in app
 * memory. Content-Length is rejected up front when available, and the stream is
 * cancelled as soon as the running byte count crosses the cap.
 */
export async function readJsonBodyLimited(
  req: Request,
  maxBytes: number
): Promise<unknown> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0) {
    throw new RangeError("maxBytes must be a positive safe integer.");
  }

  const declared = req.headers.get("content-length");
  if (declared && /^\d+$/.test(declared.trim())) {
    const declaredBytes = Number(declared);
    if (!Number.isSafeInteger(declaredBytes) || declaredBytes > maxBytes) {
      throw new JsonBodyTooLargeError(maxBytes);
    }
  }

  if (!req.body) throw new InvalidJsonBodyError();

  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel("request body too large").catch(() => undefined);
        throw new JsonBodyTooLargeError(maxBytes);
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return JSON.parse(text);
  } catch (err) {
    if (err instanceof JsonBodyTooLargeError) throw err;
    throw new InvalidJsonBodyError();
  }
}
