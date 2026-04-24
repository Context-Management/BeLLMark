// frontend/src/components/ui/provider-logo.tsx
import { cn } from '@/lib/utils';

interface ProviderLogoProps {
  provider: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const LOGO_PATHS: Record<string, string> = {
  openai: '/logos/openai.svg',
  anthropic: '/logos/anthropic.svg',
  google: '/logos/google.svg',
  deepseek: '/logos/deepseek.svg',
  grok: '/logos/grok.svg',
  glm: '/logos/glm.svg',
  kimi: '/logos/kimi.svg',
  mistral: '/logos/mistral.svg',
  lmstudio: '/logos/lmstudio.svg',
  openrouter: '/logos/openrouter.svg',
  ollama: '/logos/ollama.svg',
};

const SIZE_CLASSES = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6',
};

export function ProviderLogo({ provider, className, size = 'md' }: ProviderLogoProps) {
  const logoPath = LOGO_PATHS[provider.toLowerCase()];

  if (!logoPath) {
    // Fallback: first letter of provider
    return (
      <span className={cn(
        'inline-flex items-center justify-center rounded bg-stone-200 dark:bg-gray-700 text-xs font-bold',
        SIZE_CLASSES[size],
        className
      )}>
        {provider.charAt(0).toUpperCase()}
      </span>
    );
  }

  return (
    <img
      src={logoPath}
      alt={`${provider} logo`}
      className={cn(SIZE_CLASSES[size], 'inline-block', className)}
    />
  );
}
