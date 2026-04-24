export function buildPromptPreview(content: string, maxLines: number = 3): string {
  const lines = content.split('\n');
  if (lines.length <= maxLines) {
    return content;
  }

  return `${lines.slice(0, maxLines).join('\n')}…`;
}
