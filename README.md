# Theia-LLaMA2

https://theia-ai.org

Try Theia Chat: https://chat.theia-ai.org

This is a monorepo for building multiple Llama models:

- llama-2-13b
- llama-2-13b-chat
- llama-2-13b-transformers
- llama-2-70b
- llama-2-70b-chat
- llama-2-7b
- llama-2-7b-chat
- llama-2-7b-transformers
- llama-2-7b-vllm

---


**NOTE: Experimental branch that depends on exllama**

For now, you should:
```sh
git clone https://github.com/turboderp/exllama
cd exllama
git checkout e8a544f95b3fd64dfa5549eeeafb85b1ac71a793
```

**This template works with LLaMA 1 & 2 versions.**

This template can be used to run the `7B`, `13B`, and `70B` versions of LLaMA and LLaMA2 and it also works with fine-tuned models.

**Note: Please verify the system prompt for LLaMA or LLAMA2 and update it accordingly.**

**Note: LLaMA is for research purposes only. It is not intended for commercial use. Check the license of LLaMA & LLaMA2 on the official LLaMA website of Meta Platforms, Inc.**

## Prerequisites

- **LLaMA weights**. The weights for LLaMA have not yet been released publicly. To apply for access, fill out the Meta Research form to be able to download the weights.
- **GPU machine**. You'll need a Linux machine with an NVIDIA GPU attached and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html#docker) installed.
- **Docker**.
