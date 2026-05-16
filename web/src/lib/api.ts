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

/**
 * Sends a question to the Assest backend.
 */
export async function askQuestion(payload: AskQuestionPayload): Promise<QueryResponse> {
  // Using localhost:8000 for local dev
  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  
  const response = await fetch(`${API_URL}/api/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.NEXT_PUBLIC_API_KEY || 'assest_secret_key',
    },
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
