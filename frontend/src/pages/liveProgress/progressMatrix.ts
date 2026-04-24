export interface ProgressLabelParts {
  name: string;
  format?: string;
  quant?: string;
  host?: string;
}

export const PROGRESS_MATRIX_META_COLUMNS = 3;

/** Parse "Name (FORMAT QUANT @ host)" into stable matrix columns. */
export function parseModelLabel(label: string): ProgressLabelParts {
  if (!label.endsWith(')')) return { name: label };

  const suffixStart = label.lastIndexOf(' (');
  if (suffixStart === -1) return { name: label };

  const name = label.slice(0, suffixStart);
  const meta = label.slice(suffixStart + 2, -1);
  const atParts = meta.split(' @ ');
  const host = atParts.length > 1 ? atParts[atParts.length - 1] : undefined;
  const fmtQuant = atParts[0].trim();
  const tokens = fmtQuant.split(/\s+/);
  const formats = new Set(['GGUF', 'MLX', 'GPTQ', 'AWQ', 'EXL2']);

  let format: string | undefined;
  let quant: string | undefined;

  if (tokens.length >= 2 && formats.has(tokens[0])) {
    format = tokens[0];
    quant = tokens.slice(1).join(' ');
  } else if (tokens.length === 1) {
    if (formats.has(tokens[0])) format = tokens[0];
    else quant = tokens[0];
  }

  return { name, format, quant, host };
}

export function getProgressMatrixTemplate(questionCount: number): string {
  return `1rem minmax(18rem, max-content) max-content repeat(${questionCount}, 0.875rem)`;
}
