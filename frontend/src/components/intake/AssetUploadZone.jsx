import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, Image as ImageIcon } from "lucide-react";

const MAX_FILES = 5;
const MAX_SIZE = 10 * 1024 * 1024;
const ACCEPT = { "image/png": [], "image/jpeg": [], "image/webp": [] };

export default function AssetUploadZone({ files, onChange }) {
  const onDrop = useCallback(
    (accepted) => {
      const total = [...files, ...accepted].slice(0, MAX_FILES);
      onChange(total);
    },
    [files, onChange],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxSize: MAX_SIZE,
    maxFiles: MAX_FILES - files.length,
  });

  const remove = (idx) => {
    onChange(files.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200
          ${
            isDragActive
              ? "border-brand-accent bg-brand-accent/5"
              : "border-brand-border hover:border-brand-accent/40"
          }`}
      >
        <input {...getInputProps()} aria-label="Upload brand assets" />
        <Upload className="mx-auto mb-2 text-brand-muted" size={28} />
        <p className="text-sm text-brand-muted">
          {isDragActive
            ? "Drop files here..."
            : "Drag logos, references, or competitor ads"}
        </p>
        <p className="text-xs text-brand-muted/60 mt-1">
          PNG, JPEG, WebP. Max 5 files, 10MB each.
        </p>
      </div>

      {files.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {files.map((file, i) => (
            <div
              key={`${file.name}-${i}`}
              className="relative group w-16 h-16 rounded-lg overflow-hidden border border-brand-border"
            >
              <img
                src={URL.createObjectURL(file)}
                alt={file.name}
                className="w-full h-full object-cover"
              />
              <button
                type="button"
                onClick={() => remove(i)}
                aria-label={`Remove ${file.name}`}
                className="absolute -top-1 -right-1 bg-brand-danger rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
