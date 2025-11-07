import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
peft = pytest.importorskip("peft")

AutoModelForCausalLM = transformers.AutoModelForCausalLM
AutoTokenizer = transformers.AutoTokenizer
LoraConfig = peft.LoraConfig
get_peft_model = peft.get_peft_model


@pytest.mark.gpu
def test_lora_adapter_merge_changes_logits():
    """LoRA adapter merge should change model logits."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA required")
    device = torch.device("cuda")
    model = AutoModelForCausalLM.from_pretrained("sshleifer/tiny-gpt2").to(device)
    tokenizer = AutoTokenizer.from_pretrained("sshleifer/tiny-gpt2")

    inputs = tokenizer("Hello", return_tensors="pt").to(device)
    with torch.no_grad():
        base_logits = model(**inputs).logits

    config = LoraConfig(
        r=1,
        lora_alpha=1,
        lora_dropout=0.0,
        bias="none",
        target_modules=["c_attn"],
        layers_to_transform=[0],
    )
    lora_model = get_peft_model(model, config)
    # Make LoRA weights non-zero so merge has an effect
    for name, param in lora_model.named_parameters():
        if "lora_" in name:
            param.data.fill_(0.5)

    merged_model = lora_model.merge_and_unload()
    with torch.no_grad():
        merged_logits = merged_model(**inputs).logits

    shift = (merged_logits - base_logits).abs().max().item()
    assert shift != 0
