"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import AuthForm from "@/components/AuthForm";
import AskQuestion from "@/components/AskQuestion";
import DocumentSidebar from "@/components/DocumentSidebar";
import FileUpload from "@/components/FileUpload";
import LoadingBar from "@/components/LoadingBar";
import Summary from "@/components/Summary";
import {
  addUnauthorizedListener,
  apiFetch,
  clearStoredToken,
  getApiErrorMessage,
  getStoredToken,
  setStoredToken,
} from "@/lib/api";

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
  const [token, setToken] = useState<string | null>(null);
  const [authInitialized, setAuthInitialized] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminStatusError, setAdminStatusError] = useState("");
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
  const sessionVersion = useRef(0);

  useEffect(() => {
    const removeUnauthorizedListener = addUnauthorizedListener(() => {
      sessionVersion.current += 1;
      activeDocumentId.current = null;
      setToken(null);
      setIsAdmin(false);
      setAdminStatusError("");
      setDocuments([]);
      setSelectedDocumentId(null);
      setSelectedFile(null);
      setSummaryData(null);
      setMessages([]);
      setWorkspaceError("");
      setSidebarError("");
      setIsLoadingDocuments(false);
      setIsLoadingDocument(false);
      setIsSummarizing(false);
      setIsAsking(false);
    });
    const initializationTimer = window.setTimeout(() => {
      setToken(getStoredToken());
      setAuthInitialized(true);
    }, 0);

    return () => {
      window.clearTimeout(initializationTimer);
      removeUnauthorizedListener();
    };
  }, []);

  useEffect(() => {
    if (!authInitialized || !token) {
      return;
    }

    let isCurrent = true;
    const checkAdminStatus = async () => {
      setAdminStatusError("");
      try {
        const response = await apiFetch("/auth/me");
        if (!response.ok) {
          if (response.status !== 401) {
            setAdminStatusError(
              await getApiErrorMessage(
                response,
                "Unable to check administrator access.",
              ),
            );
          }
          return;
        }

        const currentUser: { is_admin: boolean } = await response.json();
        if (isCurrent) setIsAdmin(currentUser.is_admin);
      } catch (error: unknown) {
        if (isCurrent) {
          setAdminStatusError(
            error instanceof Error
              ? error.message
              : "Unable to check administrator access.",
          );
        }
      }
    };

    void checkAdminStatus();
    return () => {
      isCurrent = false;
    };
  }, [authInitialized, token]);

  const refreshDocuments = useCallback(async () => {
    const requestVersion = sessionVersion.current;
    setIsLoadingDocuments(true);
    setSidebarError("");

    try {
      const response = await apiFetch("/documents");
      if (!response.ok) {
        throw new Error(
          await getApiErrorMessage(response, "Failed to load your PDFs."),
        );
      }
      if (sessionVersion.current !== requestVersion) return;
      setDocuments((await response.json()) as DocumentItem[]);
    } catch (error: unknown) {
      if (sessionVersion.current === requestVersion) {
        setSidebarError(
          error instanceof Error ? error.message : "Failed to load your PDFs.",
        );
      }
    } finally {
      if (sessionVersion.current === requestVersion) {
        setIsLoadingDocuments(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!authInitialized || !token) return;
    const refreshTimer = window.setTimeout(() => {
      void refreshDocuments();
    }, 0);
    return () => window.clearTimeout(refreshTimer);
  }, [authInitialized, refreshDocuments, token]);

  const clearDocumentView = () => {
    activeDocumentId.current = null;
    setSelectedDocumentId(null);
    setSelectedFile(null);
    setSummaryData(null);
    setMessages([]);
    setWorkspaceError("");
    setIsLoadingDocument(false);
  };

  const handleAuthenticated = (accessToken: string) => {
    sessionVersion.current += 1;
    setStoredToken(accessToken);
    setToken(accessToken);
  };

  const handleLogout = () => {
    sessionVersion.current += 1;
    clearStoredToken();
    setToken(null);
    setIsAdmin(false);
    setAdminStatusError("");
    setDocuments([]);
    clearDocumentView();
    setSidebarError("");
    setIsLoadingDocuments(false);
    setIsLoadingDocument(false);
    setIsSummarizing(false);
    setIsAsking(false);
  };

  const handleNewPdf = () => {
    clearDocumentView();
  };

  const handleSelectFile = (file: File | null) => {
    clearDocumentView();
    setSelectedFile(file);
  };

  const loadDocument = async (documentId: number) => {
    const requestVersion = sessionVersion.current;
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
        sessionVersion.current === requestVersion &&
        activeDocumentId.current === documentId
      ) {
        setSummaryData(document.summary);
        setMessages(document.messages);
      }
    } catch (error: unknown) {
      if (
        sessionVersion.current === requestVersion &&
        activeDocumentId.current === documentId
      ) {
        setWorkspaceError(
          error instanceof Error ? error.message : "Failed to load this PDF.",
        );
      }
    } finally {
      if (
        sessionVersion.current === requestVersion &&
        activeDocumentId.current === documentId
      ) {
        setIsLoadingDocument(false);
      }
    }
  };

  const handleSummarize = async () => {
    if (!selectedFile) return;

    const requestVersion = sessionVersion.current;
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
      if (sessionVersion.current !== requestVersion) return;

      const summary = (await response.json()) as SummaryData & {
        document_id: number;
      };
      setSelectedFile(null);
      await Promise.all([
        refreshDocuments(),
        loadDocument(summary.document_id),
      ]);
    } catch (error: unknown) {
      if (sessionVersion.current === requestVersion) {
        setWorkspaceError(
          error instanceof Error
            ? error.message
            : "An unexpected error occurred.",
        );
      }
    } finally {
      if (sessionVersion.current === requestVersion) {
        setIsSummarizing(false);
      }
    }
  };

  const handleAsk = async (question: string) => {
    if (selectedDocumentId === null) {
      throw new Error("Select or summarize a PDF before asking a question.");
    }

    const formData = new FormData();
    const requestVersion = sessionVersion.current;
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
      sessionVersion.current !== requestVersion ||
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

    const requestVersion = sessionVersion.current;
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
      if (sessionVersion.current !== requestVersion) return;

      if (selectedDocumentId === documentId) {
        clearDocumentView();
      }
      await refreshDocuments();
    } catch (error: unknown) {
      if (sessionVersion.current === requestVersion) {
        setSidebarError(
          error instanceof Error ? error.message : "Failed to delete this PDF.",
        );
      }
    } finally {
      if (sessionVersion.current === requestVersion) {
        setDeletingDocumentId(null);
      }
    }
  };

  if (!authInitialized) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-gray-500">
        Loading...
      </main>
    );
  }

  if (!token) {
    return <AuthForm onAuthenticated={handleAuthenticated} />;
  }

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
        onLogout={handleLogout}
      />

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        <h1 className="mb-8 text-center text-3xl font-bold text-gray-900">
          AI Document Assistant
        </h1>
        {isAdmin && (
          <div className="mb-6 text-right">
            <Link
              href="/admin"
              className="inline-flex rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              Admin page
            </Link>
          </div>
        )}
        {adminStatusError && (
          <p role="alert" className="mb-6 text-sm text-red-700">
            {adminStatusError}
          </p>
        )}

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
