export async function request(
  base: string,
  token: string,
  path: string,
  method = "GET",
  body?: unknown,
) {
  if (!base) throw new Error("Set your API URL and sign in in Settings first.");
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    body instanceof FormData ? 120000 : 45000,
  );
  try {
    const response = await fetch(base.replace(/\/$/, "") + path, {
      method,
      signal: controller.signal,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
      },
      ...(body === undefined
        ? {}
        : { body: body instanceof FormData ? body : JSON.stringify(body) }),
    });
    if (!response.ok) {
      let detail = "";
      try {
        const json = await response.json();
        detail =
          typeof json.detail === "string"
            ? json.detail
            : JSON.stringify(json.detail);
      } catch {}
      const error = new Error(
        detail || `Request failed (${response.status})`,
      ) as Error & { status: number };
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : await response.json();
  } catch (e) {
    if (controller.signal.aborted)
      throw new Error(
        method === "GET"
          ? "The server took too long to respond. Try refreshing."
          : "The request timed out. It may have reached the server. Refresh and check its status before trying again.",
      );
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export async function fileForm(
  uri: string,
  name: string,
  mime: string,
  web: boolean,
) {
  const form = new FormData();
  if (web) {
    form.append("file", await (await fetch(uri)).blob(), name);
  } else {
    form.append("file", { uri, name, type: mime } as any);
  }
  return form;
}
