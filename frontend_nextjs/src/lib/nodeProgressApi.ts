// frontend_nextjs/src/lib/nodeProgressApi.ts
import { supabase } from './supabaseClient';

export type NodeStatus = "not_started" | "learning" | "mastered";

export type NodeProgress = {
  status: NodeStatus;
  score: number; // luôn có number, UI có thể convert null -> 0 nếu cần
  passed: boolean;
};

// map score sang status
function mapScoreToStatus(score: number | null | undefined): NodeStatus {
  if (score === null || score === undefined || score === 0) return "not_started";
  if (score >= 80) return "mastered";
  return "learning";
}

// ===============================
// 1) OPEN NODE
// ===============================
export async function openNode(userId: string, nodeId: string): Promise<NodeProgress> {
  try {
    await supabase.rpc('upsert_node_progress', {
      p_user_id: userId,
      p_node_id: nodeId,
      p_score: 0, // mở node mặc định score = 0
    });

    return {
      status: "learning",
      score: 0,
      passed: false,
    };
  } catch (err) {
    console.error('openNode error:', err);
    throw err;
  }
}

// ===============================
// 2) UPDATE SCORE
// ===============================
export async function updateNodeScore(userId: string, nodeId: string, score: number): Promise<NodeProgress> {
  try {
    await supabase.rpc('upsert_node_progress', {
      p_user_id: userId,
      p_node_id: nodeId,
      p_score: score,
    });

    return {
      status: mapScoreToStatus(score),
      score,
      passed: score >= 80,
    };
  } catch (err) {
    console.error('updateNodeScore error:', err);
    throw err;
  }
}

// ===============================
// 3) GET PROGRESS
// ===============================
export async function getNodeProgress(userId: string): Promise<Record<string, NodeProgress>> {
  try {
    const { data, error } = await supabase
      .from('node_progress')
      .select('node_id, score')
      .eq('user_id', userId);

    if (error) throw error;

    const result: Record<string, NodeProgress> = {};
    (data || []).forEach((row: any) => {
      result[row.node_id] = {
        status: mapScoreToStatus(row.score),
        score: row.score,
        passed: row.score >= 80,
      };
    });

    return result;
  } catch (err) {
    console.error('getNodeProgress error:', err);
    throw err;
  }
}
