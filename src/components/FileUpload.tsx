"use client";

import { useEffect, useRef } from "react";

interface FileUploadProps {
  selectedFile: File | null;
  onSelectFile: (file: File | null) => void;
  onSummarize: () => void;
  isSummarizing: boolean;
  disabled: boolean;
}

export default function FileUpload({
  selectedFile,
  onSelectFile,
  onSummarize,
  isSummarizing,
  disabled,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!selectedFile && inputRef.current) {
      inputRef.current.value = "";
    }
  }, [selectedFile]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (file && file.type !== "application/pdf") {
      alert("Please select a PDF file.");
      e.target.value = "";
      return;
    }
    onSelectFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (disabled) return;
    const file = e.dataTransfer.files?.[0] ?? null;
    if (file && file.type !== "application/pdf") {
      alert("Please select a PDF file.");
      return;
    }
    onSelectFile(file);
  };

  return (
    <div className="space-y-4">
      <label className="block text-sm font-medium text-gray-700">
        Upload PDF
      </label>

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => {
          if (!disabled) inputRef.current?.click();
        }}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-8 text-center transition-colors ${
          disabled
            ? "cursor-not-allowed opacity-60"
            : "cursor-pointer hover:border-blue-400 hover:bg-blue-50"
        }`}
      >
        <svg
          className="mb-3 h-10 w-10 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <p className="text-sm text-gray-600">
          <span className="font-medium text-blue-600">Click to upload</span> or
          drag and drop
        </p>
        <p className="mt-1 text-xs text-gray-500">PDF files only</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          disabled={disabled}
          className="hidden"
        />
      </div>

      {selectedFile && (
        <div className="flex items-center justify-between rounded-md bg-green-50 px-4 py-3">
          <span className="text-sm text-green-700">
            <span className="font-medium">Selected file:</span>{" "}
            {selectedFile.name}
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              onSelectFile(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
            className="text-sm text-gray-500 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Remove
          </button>
        </div>
      )}

      <button
        type="button"
        onClick={onSummarize}
        disabled={!selectedFile || disabled || isSummarizing}
        className="w-full rounded-md bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isSummarizing ? (
          <>
            <span className="btn-spinner" />
            Analyzing document...
          </>
        ) : (
          "Summarize PDF"
        )}
      </button>
    </div>
  );
}
