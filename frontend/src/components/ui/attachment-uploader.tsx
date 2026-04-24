import * as React from "react"
import { Upload, X, FileText, Image as ImageIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { attachmentsApi } from "@/lib/api"

// Generic attachment interface compatible with API types
export interface Attachment {
  id: number
  filename: string
  mime_type: string
  size_bytes: number
  created_at?: string
  [key: string]: unknown  // Allow additional fields from API
}

export interface AttachmentUploaderProps {
  onUpload: (attachment: Attachment) => void | Promise<void>
  accept?: string
  maxSize?: number
  disabled?: boolean
  className?: string
}

export function AttachmentUploader({
  onUpload,
  accept = ".txt,.md,.png,.jpg,.jpeg,.gif,.webp",
  maxSize = 10 * 1024 * 1024,
  disabled = false,
  className,
}: AttachmentUploaderProps) {
  const [uploading, setUploading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [dragActive, setDragActive] = React.useState(false)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleFileSelect = React.useCallback(
    async (file: File) => {
      if (!file) return

      // Validate size
      if (file.size > maxSize) {
        setError(`File too large. Max size: ${formatFileSize(maxSize)}`)
        return
      }

      setUploading(true)
      setError(null)

      try {
        const res = await attachmentsApi.upload(file)
        onUpload(res.data)
      } catch (err) {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setError(detail || (err instanceof Error ? err.message : "Upload failed"))
      } finally {
        setUploading(false)
        // Reset input
        if (inputRef.current) {
          inputRef.current.value = ""
        }
      }
    },
    [onUpload, maxSize]
  )

  const handleInputChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        handleFileSelect(file)
      }
    },
    [handleFileSelect]
  )

  const handleDrag = React.useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true)
    } else if (e.type === "dragleave") {
      setDragActive(false)
    }
  }, [])

  const handleDrop = React.useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setDragActive(false)

      if (disabled || uploading) return

      const file = e.dataTransfer.files?.[0]
      if (file) {
        handleFileSelect(file)
      }
    },
    [disabled, uploading, handleFileSelect]
  )

  return (
    <div className={cn("space-y-2", className)}>
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={cn(
          "relative rounded-md border-2 border-dashed transition-colors",
          dragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25",
          disabled || uploading ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleInputChange}
          disabled={disabled || uploading}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
        />
        <div className="p-6 text-center">
          <div className="flex justify-center mb-3">
            <Upload className="h-10 w-10 text-muted-foreground" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium">
              {uploading ? "Uploading..." : "Drop file here or click to browse"}
            </p>
            <p className="text-xs text-muted-foreground">
              Max size: {formatFileSize(maxSize)}
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-destructive">
          <X className="h-4 w-4" />
          {error}
        </div>
      )}
    </div>
  )
}

// Compact button variant for inline use
export interface AttachmentButtonProps {
  onUpload: (attachment: Attachment) => void | Promise<void>
  accept?: string
  maxSize?: number
  disabled?: boolean
  variant?: "default" | "outline" | "ghost"
  size?: "default" | "sm" | "lg"
}

export function AttachmentButton({
  onUpload,
  accept = ".txt,.md,.png,.jpg,.jpeg,.gif,.webp",
  maxSize = 10 * 1024 * 1024,
  disabled = false,
  variant = "outline",
  size = "sm",
}: AttachmentButtonProps) {
  const [uploading, setUploading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const handleFileSelect = React.useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return

      if (file.size > maxSize) {
        setError(`File too large. Max: ${Math.round(maxSize / (1024 * 1024))}MB`)
        return
      }

      setUploading(true)
      setError(null)

      try {
        const res = await attachmentsApi.upload(file)
        onUpload(res.data)
      } catch (err) {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setError(detail || (err instanceof Error ? err.message : "Upload failed"))
      } finally {
        setUploading(false)
        if (inputRef.current) {
          inputRef.current.value = ""
        }
      }
    },
    [onUpload, maxSize]
  )

  return (
    <div className="space-y-2">
      <div className="relative">
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleFileSelect}
          disabled={disabled || uploading}
          className="hidden"
        />
        <Button
          type="button"
          variant={variant}
          size={size}
          disabled={disabled || uploading}
          onClick={() => inputRef.current?.click()}
        >
          <Upload className="h-4 w-4 mr-2" />
          {uploading ? "Uploading..." : "Upload File"}
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

// Attachment display item
export interface AttachmentItemProps {
  attachment: Attachment
  onRemove?: () => void
  className?: string
}

export function AttachmentItem({
  attachment,
  onRemove,
  className,
}: AttachmentItemProps) {
  const isImage = attachment.mime_type.startsWith("image/")

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div
      className={cn(
        "flex items-center gap-3 p-3 rounded-md border bg-card text-card-foreground",
        className
      )}
    >
      <div className="flex-shrink-0">
        {isImage ? (
          <ImageIcon className="h-5 w-5 text-muted-foreground" />
        ) : (
          <FileText className="h-5 w-5 text-muted-foreground" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{attachment.filename}</p>
        <p className="text-xs text-muted-foreground">
          {formatFileSize(attachment.size_bytes)}
        </p>
      </div>
      {onRemove && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onRemove}
          className="flex-shrink-0 h-8 w-8 p-0"
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
