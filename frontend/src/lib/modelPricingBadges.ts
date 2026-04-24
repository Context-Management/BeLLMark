export type PricingBadgeTone = 'input' | 'output' | 'source';

export type PricingBadgeModel = {
  price_input: number | null | undefined;
  price_output: number | null | undefined;
  price_currency: string | null | undefined;
  price_source?: string | null | undefined;
  price_source_url?: string | null | undefined;
  price_checked_at?: string | null | undefined;
};

export type PricingBadge = {
  key: 'input' | 'output' | 'source';
  label: string;
  tone: PricingBadgeTone;
  href?: string;
  title?: string;
};

export function formatPricingUnitLabel(currency: string | null | undefined): string {
  if (!currency) return 'price (/1M tokens)';
  if (currency === 'USD') return 'price ($/1M tokens)';
  return `price (${currency}/1M tokens)`;
}

function formatCurrencyPrefix(currency: string | null | undefined): string {
  if (!currency || currency === 'USD') return '$';
  return `${currency} `;
}

function formatCheckedAt(value: string | null | undefined): string | null {
  if (!value) return null;
  const normalized = value.includes('T') ? value.slice(0, 10) : value;
  return normalized || null;
}

export function getModelPricingBadges(model: PricingBadgeModel): PricingBadge[] {
  if (model.price_input == null || model.price_output == null) return [];

  const currencyPrefix = formatCurrencyPrefix(model.price_currency);
  const badges: PricingBadge[] = [
    {
      key: 'input',
      label: `in ${currencyPrefix}${model.price_input.toFixed(2)}`,
      tone: 'input',
    },
    {
      key: 'output',
      label: `out ${currencyPrefix}${model.price_output.toFixed(2)}`,
      tone: 'output',
    },
  ];

  if (model.price_source) {
    const checkedAt = formatCheckedAt(model.price_checked_at);
    const sourceBadge: PricingBadge = {
      key: 'source',
      label: model.price_source,
      tone: 'source',
      title: checkedAt ? `${model.price_source} · checked ${checkedAt}` : model.price_source,
    };
    if (model.price_source_url) {
      sourceBadge.href = model.price_source_url;
    }
    badges.push(sourceBadge);
  }

  return badges;
}
