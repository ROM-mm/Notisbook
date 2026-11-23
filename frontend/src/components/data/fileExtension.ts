/** Extensão em minúsculas após o último ".", ou "" — um oculto como ".env" (ponto inicial) não tem extensão. */
export function extension(name: string): string {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(i + 1).toLowerCase() : "";
}
