"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AskQuestion from "@/components/AskQuestion";
import DocumentSidebar from "@/components/DocumentSidebar";
import FileUpload from "@/components/FileUpload";
import LoadingBar from "@/components/LoadingBar";
import Summary from "@/components/Summary";
import { apiFetch, getApiErrorMessage } from "@/lib/api";

interface SummaryData {
  summary: string;
  key_points: string[];
  key_takeaways: string[];
}

interface DocumentItem {
  id: number;
  filename: string;
  created_at: string;
  has_summary: boolean;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

interface SavedDocumentResponse {
  document_id: number;
  filename: string;
  summary: SummaryData | null;
  messages: ChatMessage[];
}

export default function Home() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(
    null,
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [summaryData, setSummaryData] = useState<SummaryData | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isLoadingDocument, setIsLoadingDocument] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(
    null,
  );
  const [workspaceError, setWorkspaceError] = useState("");
  const [sidebarError, setSidebarError] = useState("");
  const activeDocumentId = useRef<number | null>(null);
  const workspaceVersion = useRef(0);

  const refreshDocuments = useCallback(async () => {
    const requestVersion = workspaceVersion.current;
    setIsLoadingDocuments(true);
    setSidebarError("");

    try {
      const response = await apiFetch("/documents");
      if (!response.ok) {
        throw new Error(
          await getApiErrorMessage(response, "Failed to load your PDFs."),
        );
      }
      if (workspaceVersion.current !== requestVersion) return;
      setDocuments((await response.json()) as DocumentItem[]);
    } catch (error: unknown) {
      if (workspaceVersion.current === requestVersion) {
        setSidebarError(
          error instanceof Error ? error.message : "Failed to load your PDFs.",
        );
      }
    } finally {
      if (workspaceVersion.current === requestVersion) {
        setIsLoadingDocuments(false);
      }
    }
  }, []);

  useEffect(() => {
    const refreshTimer = window.setTimeout(() => {
      void refreshDocuments();
    }, 0);
    return () => window.clearTimeout(refreshTimer);
  }, [refreshDocuments]);

  const clearDocumentView = () => {
    activeDocumentId.current = null;
    setSelectedDocumentId(null);
    setSelectedFile(null);
    setSummaryData(null);
    setMessages([]);
    setWorkspaceError("");
    setIsLoadingDocument(false);
    workspaceVersion.current += 1;
  };

  const handleNewPdf = () => {
    clearDocumentView();
  };

  const handleSelectFile = (file: File | null) => {
    clearDocumentView();
    setSelectedFile(file);
  };

  const loadDocument = async (documentId: number) => {
    const requestVersion = workspaceVersion.current;
    activeDocumentId.current = documentId;
    setSelectedDocumentId(documentId);
    setSelectedFile(null);
    setSummaryData(null);
    setMessages([]);
    setWorkspaceError("");
    setIsLoadingDocument(true);

    try {
      const response = await apiFetch(
        `/documents/${documentId}/messages`,
      );
      if (!response.ok) {
        throw new Error(
          await getApiErrorMessage(response, "Failed to load this PDF."),
        );
      }

      const document =
        (await response.json()) as SavedDocumentResponse;
      if (
        workspaceVersion.current === requestVersion &&
        activeDocumentId.current === documentId
      ) {
        setSummaryData(document.summary);
        setMessages(document.messages);
      }
    } catch (error: unknown) {
      if (
        workspaceVersion.current === requestVersion &&
        activeDocumentId.current === documentId
      ) {
        setWorkspaceError(
          error instanceof Error ? error.message : "Failed to load this PDF.",
        );
      }
    } finally {
      if (
        workspaceVersion.current === requestVersion &&
        activeDocumentId.current === documentId
      ) {
        setIsLoadingDocument(false);
      }
    }
  };

  const handleSummarize = async () => {
    if (!selectedFile) return;

    const requestVersion = workspaceVersion.current;
    setIsSummarizing(true);
    setWorkspaceError("");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await apiFetch("/summarize", {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(
          await getApiErrorMessage(
            response,
            "Failed to summarize the document.",
          ),
        );
      }
      if (workspaceVersion.current !== requestVersion) return;

      const summary = (await response.json()) as SummaryData & {
        document_id: number;
      };
      setSelectedFile(null);
      await Promise.all([
        refreshDocuments(),
        loadDocument(summary.document_id),
      ]);
    } catch (error: unknown) {
      if (workspaceVersion.current === requestVersion) {
        setWorkspaceError(
          error instanceof Error
            ? error.message
            : "An unexpected error occurred.",
        );
      }
    } finally {
      if (workspaceVersion.current === requestVersion) {
        setIsSummarizing(false);
      }
    }
  };

  const handleAsk = async (question: string) => {
    if (selectedDocumentId === null) {
      throw new Error("Select or summarize a PDF before asking a question.");
    }

    const formData = new FormData();
    const requestVersion = workspaceVersion.current;
    formData.append("document_id", String(selectedDocumentId));
    formData.append("question", question);

    const response = await apiFetch("/ask", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(
        await getApiErrorMessage(response, "Failed to get an answer."),
      );
    }

    const result: { answer: string } = await response.json();
    if (
      workspaceVersion.current !== requestVersion ||
      selectedDocumentId !== Number(formData.get("document_id"))
    ) {
      return "";
    }
    const timestamp = new Date().toISOString();
    setMessages((currentMessages) => [
      ...currentMessages,
      { role: "user", content: question, created_at: timestamp },
      { role: "assistant", content: result.answer, created_at: timestamp },
    ]);
    return result.answer;
  };

  const handleDeleteDocument = async (documentId: number) => {
    if (!window.confirm("Delete this PDF and its chat history?")) return;

    const requestVersion = workspaceVersion.current;
    setDeletingDocumentId(documentId);
    setSidebarError("");
    try {
      const response = await apiFetch(`/documents/${documentId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(
          await getApiErrorMessage(response, "Failed to delete this PDF."),
        );
      }
      if (workspaceVersion.current !== requestVersion) return;

      if (selectedDocumentId === documentId) {
        clearDocumentView();
      }
      await refreshDocuments();
    } catch (error: unknown) {
      if (workspaceVersion.current === requestVersion) {
        setSidebarError(
          error instanceof Error ? error.message : "Failed to delete this PDF.",
        );
      }
    } finally {
      if (workspaceVersion.current === requestVersion) {
        setDeletingDocumentId(null);
      }
    }
  };

  const isBusy =
    isLoadingDocuments ||
    isSummarizing ||
    isAsking ||
    isLoadingDocument ||
    deletingDocumentId !== null;

  return (
    <div className="flex min-h-screen flex-col bg-gray-50 md:flex-row">
      <LoadingBar isLoading={isBusy} />
      <DocumentSidebar
        documents={documents}
        selectedDocumentId={selectedDocumentId}
        isLoading={isLoadingDocuments}
        isBusy={isBusy}
        deletingDocumentId={deletingDocumentId}
        error={sidebarError}
        onNewPdf={handleNewPdf}
        onSelectDocument={(documentId) => void loadDocument(documentId)}
        onDeleteDocument={handleDeleteDocument}
      />

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        <h1 className="mb-8 text-center text-3xl font-bold text-gray-900">
          AI Document Assistant
        </h1>

        <div className="space-y-8">
          <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <FileUpload
              selectedFile={selectedFile}
              onSelectFile={handleSelectFile}
              onSummarize={handleSummarize}
              isSummarizing={isSummarizing}
              disabled={isBusy}
            />
          </section>

          {workspaceError && (
            <div
              role="alert"
              className="rounded-md bg-red-50 p-4 text-sm text-red-700"
            >
              {workspaceError}
            </div>
          )}

          {isLoadingDocument && (
            <p className="text-sm text-gray-500">Loading saved PDF...</p>
          )}

          {summaryData && (
            <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
              <Summary
                summary={summaryData.summary}
                keyPoints={summaryData.key_points}
                keyTakeaways={summaryData.key_takeaways}
              />
            </section>
          )}

          {selectedDocumentId !== null && (
            <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
              <AskQuestion
                key={selectedDocumentId}
                documentId={selectedDocumentId}
                messages={messages}
                isAsking={isAsking}
                setIsAsking={setIsAsking}
                onAsk={handleAsk}
                disabled={isLoadingDocument || isSummarizing}
              />
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
