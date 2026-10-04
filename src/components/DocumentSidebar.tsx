"use client";

interface DocumentItem {
  id: number;
  filename: string;
  created_at: string;
  has_summary: boolean;
}

interface DocumentSidebarProps {
  documents: DocumentItem[];
  selectedDocumentId: number | null;
  isLoading: boolean;
  isBusy: boolean;
  deletingDocumentId: number | null;
  error: string;
  onNewPdf: () => void;
  onSelectDocument: (documentId: number) => void;
  onDeleteDocument: (documentId: number) => void;
}

export default function DocumentSidebar({
  documents,
  selectedDocumentId,
  isLoading,
  isBusy,
  deletingDocumentId,
  error,
  onNewPdf,
  onSelectDocument,
  onDeleteDocument,
}: DocumentSidebarProps) {
  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-gray-200 bg-white md:min-h-screen md:w-72 md:border-b-0 md:border-r">
      <div className="flex items-center justify-between border-b border-gray-100 p-4">
        <h1 className="text-base font-bold text-gray-900">
          AI Document Assistant
        </h1>
      </div>

      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Your PDFs
        </h2>
        <button
          type="button"
          onClick={onNewPdf}
          disabled={isBusy}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          New PDF
        </button>
      </div>

      {error && (
        <p role="alert" className="mx-4 mt-2 rounded-md bg-red-50 p-2 text-xs text-red-700">
          {error}
        </p>
      )}

      <nav className="max-h-64 space-y-1 overflow-y-auto px-2 pb-3 md:max-h-none md:flex-1">
        {isLoading ? (
          <p className="px-2 py-3 text-sm text-gray-500">Loading PDFs...</p>
        ) : documents.length === 0 ? (
          <p className="px-2 py-3 text-sm text-gray-500">
            Your saved PDFs will appear here.
          </p>
        ) : (
          documents.map((document) => (
            <div
              key={document.id}
              className={`flex items-center gap-2 rounded-lg px-2 py-2 ${
                selectedDocumentId === document.id
                  ? "bg-blue-50"
                  : "hover:bg-gray-50"
              }`}
            >
              <button
                type="button"
                onClick={() => onSelectDocument(document.id)}
                disabled={isBusy}
                className="min-w-0 flex-1 text-left"
              >
                <span className="block truncate text-sm font-medium text-gray-800">
                  {document.filename}
                </span>
                <span className="mt-0.5 block text-xs text-gray-500">
                  {new Date(document.created_at).toLocaleDateString()}
                </span>
              </button>
              <button
                type="button"
                onClick={() => onDeleteDocument(document.id)}
                disabled={isBusy || deletingDocumentId !== null}
                aria-label={`Delete ${document.filename}`}
                className="shrink-0 rounded px-2 py-1 text-xs text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deletingDocumentId === document.id ? "..." : "Delete"}
              </button>
            </div>
          ))
        )}
      </nav>
    </aside>
  );
}
