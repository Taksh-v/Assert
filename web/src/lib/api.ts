export interface Source {
  title: string;
  url: string;
}

export interface QueryResponse {
  answer: string;
  sources: Source[];
  query_id: string;
  conversation_id: string;
}

export interface AskQuestionPayload {
  question: string;
  workspace_id: string;
  conversation_id?: string;
}

import { apiFetch } from "./auth";

/**
 * Sends a question to the Assest backend.
 */
export async function askQuestion(payload: AskQuestionPayload): Promise<QueryResponse> {
  const response = await apiFetch("/api/query", {
    method: 'POST',
    body: JSON.stringify({
      question: payload.question,
      workspace_id: payload.workspace_id,
      conversation_id: payload.conversation_id,
      response_format: 'markdown'
    }),
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`);
  }

  return response.json();
}
