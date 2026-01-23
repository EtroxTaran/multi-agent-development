import { Injectable, Logger } from '@nestjs/common';
import { OrchestratorClientService } from '../orchestrator-client/orchestrator-client.service';
import { ChatRequestDto, ChatResponseDto, CommandRequestDto, CommandResponseDto } from './dto';

@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);

  constructor(
    private readonly orchestratorClient: OrchestratorClientService,
  ) {}

  async chat(request: ChatRequestDto): Promise<ChatResponseDto> {
    try {
      const response = await this.orchestratorClient.chat(
        request.message,
        request.projectName,
        request.context,
      ) as ChatResponseDto;
      return response;
    } catch (error: any) {
      this.logger.error(`Chat failed: ${error.message}`);
      throw error;
    }
  }

  async executeCommand(request: CommandRequestDto): Promise<CommandResponseDto> {
    try {
      const response = await this.orchestratorClient.executeCommand(
        request.command,
        request.args,
        request.projectName,
      ) as CommandResponseDto;
      return response;
    } catch (error: any) {
      this.logger.error(`Command failed: ${error.message}`);
      throw error;
    }
  }
}