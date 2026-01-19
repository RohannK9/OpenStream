export type GroupInfo = {
  name?: string;
  consumers?: number;
  pending?: number;
  lag?: number;
  "last-delivered-id"?: string;
  entries_read?: number;
};

export type PartitionStat = {
  partition: number;
  stream: string;
  length: number;
  groups: GroupInfo[];
};

export type TopicStat = {
  topic: string;
  partitions: number;
  partition_stats: PartitionStat[];
};

export type MetricsSummary = {
  topics: TopicStat[];
  redis: {
    used_memory?: number;
    used_memory_human?: string;
  };
};

