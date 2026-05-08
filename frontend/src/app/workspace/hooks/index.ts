export { useWorkspaceState } from './useWorkspaceState';
export { useEditorSetup } from './useEditorSetup';
export type { SelectionPosition } from './useEditorSetup';
export { useTextReplacement, normalizeForSearch, buildTextPositionMap } from './useTextReplacement';
export { useChatActions } from './useChatActions';
export { useAgenticChat } from './useAgenticChat';
export type { 
  AgenticEventType, 
  AgenticStatus, 
  ToolCall, 
  ToolResult, 
  AgenticEvent, 
  AgenticSession 
} from './useAgenticChat';
