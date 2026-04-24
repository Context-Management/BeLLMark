import { FileText, Image, X, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

interface Attachment {
  id: number;
  filename: string;
  mime_type: string;
  size_bytes: number;
  inherited?: boolean;  // For showing if from suite
}

interface AttachmentListProps {
  attachments: Attachment[];
  onRemove?: (id: number) => void;  // Optional - if not provided, no remove button
  showInherited?: boolean;  // Show "inherited" badge
  emptyMessage?: string;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(mimeType: string) {
  if (mimeType.startsWith('image/')) {
    return <Image className="h-4 w-4 text-blue-500" />;
  }
  return <FileText className="h-4 w-4 text-slate-400 dark:text-gray-500" />;
}

export function AttachmentList({
  attachments,
  onRemove,
  showInherited = false,
  emptyMessage = "No attachments"
}: AttachmentListProps) {
  if (attachments.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">{emptyMessage}</p>
    );
  }

  return (
    <div className="space-y-2">
      {attachments.map((attachment) => (
        <div
          key={attachment.id}
          className="flex items-center justify-between p-2 rounded-md border bg-card"
        >
          <div className="flex items-center gap-2 min-w-0">
            {getFileIcon(attachment.mime_type)}
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{attachment.filename}</p>
              <p className="text-xs text-muted-foreground">
                {formatFileSize(attachment.size_bytes)}
              </p>
            </div>
            {showInherited && attachment.inherited && (
              <Badge variant="secondary" className="text-xs">
                from suite
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={async () => {
                try {
                  const res = await api.get(`/api/attachments/${attachment.id}/download`, { responseType: 'blob' });
                  const blob = res.data as Blob;
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = attachment.filename;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                } catch (err) {
                  console.error('Download failed:', err);
                }
              }}
            >
              <Download className="h-4 w-4" />
            </Button>
            {onRemove && !attachment.inherited && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive hover:text-destructive"
                onClick={() => onRemove(attachment.id)}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
