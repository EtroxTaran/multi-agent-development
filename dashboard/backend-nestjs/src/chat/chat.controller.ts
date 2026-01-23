import { Controller, Post, Body } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { ChatService } from './chat.service';
import { ChatRequestDto, ChatResponseDto, CommandRequestDto, CommandResponseDto } from './dto';

@Controller('api/chat')
@ApiTags('chat')
export class ChatController {
  constructor(private readonly chatService: ChatService) {}

  @Post()
  @ApiOperation({ summary: 'Send a chat message' })
  @ApiResponse({
    status: 200,
    description: 'Chat response',
    type: ChatResponseDto,
  })
  async chat(@Body() request: ChatRequestDto): Promise<ChatResponseDto> {
    return this.chatService.chat(request);
  }

  @Post('command')
  @ApiOperation({ summary: 'Execute a command' })
  @ApiResponse({
    status: 200,
    description: 'Command response',
    type: CommandResponseDto,
  })
  async executeCommand(
    @Body() request: CommandRequestDto,
  ): Promise<CommandResponseDto> {
    return this.chatService.executeCommand(request);
  }
}
