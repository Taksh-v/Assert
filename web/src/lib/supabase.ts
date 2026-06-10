import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  console.error(
    'CRITICAL: Supabase environment variables are missing. ' +
    'Please check your .env.local file and ensure NEXT_PUBLIC_SUPABASE_URL ' +
    'and NEXT_PUBLIC_SUPABASE_ANON_KEY are set.'
  );
}

// Fallback to empty strings only for type safety; the error above will signal the developer
export const supabase = createClient(supabaseUrl || 'https://placeholder.supabase.co', supabaseAnonKey || 'placeholder');
