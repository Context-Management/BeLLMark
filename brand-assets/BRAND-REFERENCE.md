# BeLLMark Brand Assets

## Colors

| Name | Hex | Usage |
|------|-----|-------|
| Gold (primary) | `#D4A017` | Brand accent, bell icon fill |
| Gold Light | `#F5C842` | Gradient start |
| Gold Dark | `#A67C00` | Strokes, hover states |
| Green (check) | `#22C55E` | Checkmark, success states |
| Green Light | `#4ADE80` | Gradient start |
| Charcoal | `#1C1C1E` | Text, dark backgrounds |
| Stone | `#F5F5F4` | Light text on dark |
| White | `#FFFFFF` | Backgrounds |

## Typography

- **Primary font**: Inter (Google Fonts)
- **Logo text**: Inter Bold (700), 42px at base SVG scale
- **Casing**: BeLLMark (capital B, LL, M — never "Bellmark" or "BELLMARK")

## Logo Variants

### Wordmarks (logo + text)
| File | Use |
|------|-----|
| `bellmark-wordmark-light` | Light/white backgrounds |
| `bellmark-wordmark-dark` | Dark backgrounds |
| `bellmark-wordmark-gold` | Gold accent backgrounds |

### Logomarks (bell icon only)
| File | Use |
|------|-----|
| `bellmark-logomark-light` | Light backgrounds, favicons |
| `bellmark-logomark-dark` | Dark backgrounds |
| `bellmark-logomark-gold` | Gold accent backgrounds |
| `bellmark-logomark-green` | Green accent backgrounds |

## Sizes Available

**Wordmarks (PNG)**: 1920w, 960w, 480w — all with transparent background
**Logomarks (PNG)**: 1024px, 512px, 256px, 128px, 64px — all with transparent background
**SVG**: Vector originals in `svg/` — scale to any size

## Quick Pick Guide

| Context | Recommended Asset |
|---------|-------------------|
| Creem product logo | `logomark-light-512px.png` |
| Website header | `wordmark-light` SVG |
| Social media avatar | `logomark-light-256px.png` |
| Email signature | `wordmark-light-480w.png` |
| Presentation slides | `wordmark-light-960w.png` or `wordmark-dark-960w.png` |
| Print / high-res | SVG originals |
| Favicon | `logomark-light-64px.png` |

## Directory Structure

```
brand-assets/
├── BRAND-REFERENCE.md        ← this file
├── svg/
│   ├── wordmarks/            ← vector originals (logo + text)
│   └── logomarks/            ← vector originals (bell icon only)
├── png/
│   ├── wordmarks/            ← rasterized at 480w, 960w, 1920w
│   └── logomarks/            ← rasterized at 64px–1024px
└── screenshots/              ← product UI screenshots
```
