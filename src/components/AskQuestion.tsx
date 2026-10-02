"use client";

import { useState } from "react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

interface QuestionTurn {
  question: string;
  answer: string;
}

interface AskQuestionProps {
  documentId: number;
  messages: ChatMessage[];
  isAsking: boolean;
  setIsAsking: (value: boolean) => void;
  onAsk: (question: string) => Promise<string>;
  disabled: boolean;
}

export default function AskQuestion({
  documentId,
  messages,
  isAsking,
  setIsAsking,
  onAsk,
  disabled,
}: AskQuestionProps) {
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");

  const turns = messages.reduce<QuestionTurn[]>((currentTurns, message, index) => {
    if (message.role === "assistant") {
      const previousMessage = messages[index - 1];
      currentTurns.push({
        question:
          previousMessage?.role === "user" ? previousMessage.content : "",
        answer: message.content,
      });
    }
    return currentTurns;
  }, []);

  const handleAsk = async () => {
    if (!question.trim()) {
      setError("Please enter a question.");
      return;
    }

    const submittedQuestion = question;
    setIsAsking(true);
    setError("");
    setQuestion("");

    try {
      await onAsk(submittedQuestion);
    } catch (requestError: unknown) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : "An unexpected error occurred.";
      setError(message);
      setQuestion((currentQuestion) => currentQuestion || submittedQuestion);
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-gray-900">
          Ask About This Document
        </h3>
        <p className="mt-1 text-sm text-gray-500">
          Ask a question and get an answer based on the uploaded PDF.
        </p>
      </div>

      {turns.map((turn, index) => (
        <div key={`${documentId}-${index}`} className="space-y-2">
          <p className="text-sm font-medium text-gray-700">{turn.question}</p>
          <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-5">
            <h4 className="text-sm font-semibold text-gray-900">Answer</h4>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
              {turn.answer}
            </p>
          </div>
        </div>
      ))}

      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
            setError("");
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              void handleAsk();
            }
          }}
          placeholder="Type your question..."
          disabled={disabled || isAsking}
          className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm placeholder-gray-400 transition-colors focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void handleAsk()}
          disabled={disabled || isAsking || question.trim().length === 0}
          className="w-full shrink-0 rounded-lg bg-blue-600 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {isAsking ? "Thinking..." : "Ask"}
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {isAsking && (
        <p className="text-sm text-gray-500 italic">Thinking...</p>
      )}
    </div>
  );
}
