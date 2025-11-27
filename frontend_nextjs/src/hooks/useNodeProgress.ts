import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/lib/supabaseClient';

export type NodeStatus = 'not_started' | 'learning' | 'mastered';

export function useNodeProgress(userId: string) {
  const [progress, setProgress] = useState<Record<string, number>>({});

  const getStatus = (score: number | null | undefined): NodeStatus => {
    if (!score) return 'not_started';
    if (score >= 80) return 'mastered';
    return 'learning';
  };

  const handleOpenNode = useCallback(async (nodeId: string) => {
    try {
      await supabase.rpc('upsert_node_progress', {
        p_user_id: userId,
        p_node_id: nodeId,
        p_score: 0
      });

      setProgress(prev => ({ ...prev, [nodeId]: prev[nodeId] ?? 0 }));
    } catch (err) {
      console.error('Failed to open node:', err);
    }
  }, [userId]);

  const handleUpdateNodeScore = useCallback(async (nodeId: string, score: number) => {
    try {
      const { data, error } = await supabase.rpc('upsert_node_progress', {
        p_user_id: userId,
        p_node_id: nodeId,
        p_score: score
      });
      if (error) throw error;

      setProgress(prev => ({ ...prev, [nodeId]: score }));
    } catch (err) {
      console.error('Failed to update node score:', err);
    }
  }, [userId]);

  const fetchProgress = useCallback(async () => {
    try {
      const { data, error } = await supabase
        .from('node_progress')
        .select('node_id, score')
        .eq('user_id', userId);
      if (error) throw error;

      const newProgress: Record<string, number> = {};
      data.forEach((row: any) => {
        newProgress[row.node_id] = row.score;
      });
      setProgress(newProgress);
    } catch (err) {
      console.error('Failed to fetch node progress:', err);
    }
  }, [userId]);

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  return {
    progress,
    openNode: handleOpenNode,
    updateNodeScore: handleUpdateNodeScore,
    getStatus,
  };
}
