export const UPLOAD_LIMITS = {
  MAX_FILES_PER_UPLOAD: 10,
  MAX_TOTAL_SIZE_MB: 100,
  MAX_INDIVIDUAL_FILE_SIZE_MB: 25,
  SUPPORTED_FILE_TYPES: [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'text/csv',
    'text/html',
    'text/markdown'
  ]
} as const;

export const UPLOAD_MESSAGES = {
  TOO_MANY_FILES: (max: number) => 
    `Maximum ${max} files allowed per upload. Please select fewer files or upload in batches.`,
  TOTAL_SIZE_TOO_LARGE: (current: number, max: number) => 
    `Total file size (${current}MB) exceeds limit of ${max}MB. Please remove some files.`,
  INDIVIDUAL_FILE_TOO_LARGE: (filename: string, size: number, max: number) => 
    `File "${filename}" (${size}MB) exceeds individual file limit of ${max}MB.`,
  UNSUPPORTED_FILE_TYPE: (filename: string, type: string) => 
    `File "${filename}" has unsupported type "${type}". Please convert to a supported format.`
} as const;

// Helper functions
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

export const bytesToMB = (bytes: number): number => {
  return Math.round(bytes / (1024 * 1024));
}; 