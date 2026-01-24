/**
 * Chat panel component with Claude integration
 */

import { useState, useRef, useEffect } from "react";
import { Send, StopCircle, Trash2, AlertCircle } from "lucide-react";
import {
  useStreamingChat,
  useWorkflowStatus,
  useResumeWorkflow,
} from "@/hooks";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ScrollArea,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types";

interface ChatPanelProps {
  projectName: string;
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        <p className="whitespace-pre-wrap text-sm">{message.content}</p>
      </div>
    </div>
  );
}

export function ChatPanel({ projectName }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const {
    messages,
    currentResponse,
    isStreaming,
    sendMessage,
    stopStreaming,
    clearMessages,
  } = useStreamingChat(projectName);

  // HITL Integration
  const { data: status } = useWorkflowStatus(projectName);
  const resumeWorkflow = useResumeWorkflow(projectName);
  const isPaused = status?.status === "paused";

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, currentResponse, isPaused]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    if (isPaused) {
      // If paused, send input as resume response
      // We assume the input is the "response" field
      // The backend expects a dict, typically {"action": "approve"} or user input
      // We'll send generic structure:
      // We'll send generic structure:
      const humanResponse = {
        action: "continue",
        response: input,
      };
      resumeWorkflow.mutate(humanResponse);
      setInput("");
      return;
    }

    if (isStreaming) return;

    sendMessage(input);
    setInput("");
  };

  return (
    <Card className="h-[600px] flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <CardTitle>Chat with Claude</CardTitle>
            {isPaused && (
              <span className="flex items-center text-sm font-medium text-yellow-600 bg-yellow-50 px-2 py-1 rounded">
                <AlertCircle className="h-3 w-3 mr-1" />
                Input Required
              </span>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={clearMessages}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col overflow-hidden">
        {/* Messages */}
        <ScrollArea className="flex-1 pr-4" ref={scrollRef}>
          <div className="space-y-4">
            {messages.map((message, index) => (
              <MessageBubble key={index} message={message} />
            ))}
            {isStreaming && currentResponse && (
              <MessageBubble
                message={{
                  role: "assistant",
                  content: currentResponse + "...",
                }}
              />
            )}

            {/* System Message for Pause with Interrupt Context */}
            {isPaused && (
              <div className="flex justify-start">
                <div className="max-w-[90%] rounded-lg px-4 py-3 bg-yellow-50 border border-yellow-200 text-yellow-800">
                  <p className="font-semibold text-sm mb-2">Workflow Paused</p>
                  {status?.pending_interrupt?.question ? (
                    <>
                      <p className="text-sm mb-3">
                        {String(status.pending_interrupt.question)}
                      </p>
                      {Array.isArray(status.pending_interrupt.options) &&
                        status.pending_interrupt.options.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-2">
                            {status.pending_interrupt.options.map(
                              (opt: string) => (
                                <Button
                                  key={opt}
                                  size="sm"
                                  variant="outline"
                                  className="border-yellow-400 hover:bg-yellow-100"
                                  onClick={() => {
                                    resumeWorkflow.mutate({
                                      action: opt.toLowerCase(),
                                      response: opt,
                                    });
                                  }}
                                >
                                  {opt}
                                </Button>
                              ),
                            )}
                          </div>
                        )}
                    </>
                  ) : (
                    <p className="text-sm">
                      The workflow requires your input to continue. Please
                      provide your response below.
                    </p>
                  )}
                </div>
              </div>
            )}

            {messages.length === 0 && !isStreaming && !isPaused && (
              <div className="text-center text-muted-foreground py-8">
                <p>Start a conversation with Claude</p>
                <p className="text-sm mt-2">
                  Ask questions about this project or run commands
                </p>
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Input */}
        <form
          onSubmit={handleSubmit}
          className="flex items-center space-x-2 mt-4"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              isPaused
                ? "Enter your response to continue..."
                : "Type a message..."
            }
            className={cn(
              "flex-1 px-3 py-2 border rounded-md transition-colors",
              isPaused && "border-yellow-400 focus:ring-yellow-400",
            )}
            disabled={isStreaming && !isPaused}
          />
          {isStreaming && !isPaused ? (
            <Button type="button" variant="destructive" onClick={stopStreaming}>
              <StopCircle className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              type="submit"
              disabled={!input.trim()}
              className={cn(isPaused && "bg-yellow-600 hover:bg-yellow-700")}
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
