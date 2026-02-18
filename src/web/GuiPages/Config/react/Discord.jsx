const Discord = ({ discordConfig = {}, setDiscordConfig }) => {

    const [showDiscordDiv, setShowDiscordDiv] = React.useState(false);

    const handleEnabledChange = (e) => {
        setDiscordConfig({ ...discordConfig, enabled: e.target.checked });
    };

    const handleWebhookChange = (e) => {
        setDiscordConfig({ ...discordConfig, webhook_url: e.target.value });
    };

    const handlePingChange = (e) => {
        setDiscordConfig({ ...discordConfig, ping_user: e.target.checked });
    };

    return (
        <div className="category-container" id="discord-category">

            <div className="category-title-container">
                <span className="category-title">Discord Integration</span>
                <button className="show-hide-button" onClick={() => setShowDiscordDiv(!showDiscordDiv)}>
                    <div className={`triangle ${showDiscordDiv ? "collapse" : "expand"}`} />
                </button>
            </div>

            <CollapsibleDiv showDiv={showDiscordDiv}>
                <div className="collapsible-content-container">

                    <div className="control-group" style={{ marginTop: "10px" }}>
                        <label className="label-title">
                            <span>Enable Notifications</span>
                        </label>
                        <input
                            type="checkbox"
                            checked={discordConfig?.enabled || false}
                            onChange={handleEnabledChange}
                            style={{ marginLeft: "10px" }}
                        />
                    </div>

                    <div className="control-group">
                        <label className="label-title">
                            <span>Webhook URL</span>
                        </label>
                        <input
                            type="text"
                            className="input-text"
                            style={{ width: "90%" }}
                            value={discordConfig?.webhook_url || ""}
                            onChange={handleWebhookChange}
                            placeholder="https://discord.com/api/webhooks/..."
                        />
                    </div>

                    <div className="control-group">
                        <label className="label-title">
                            <span>Ping @everyone</span>
                        </label>
                        <input
                            type="checkbox"
                            checked={discordConfig?.ping_user || false}
                            onChange={handlePingChange}
                            style={{ marginLeft: "10px" }}
                        />
                    </div>

                    {discordConfig?.enabled && (
                        <React.Fragment>
                            <div style={{ color: "#888", fontSize: "0.8em", marginTop: "5px", marginLeft: "5px" }}>
                                Notifications will be sent for <b>S</b> and <b>A</b> tier Pokemon.
                            </div>
                        </React.Fragment>
                    )}
                </div>
            </CollapsibleDiv>
        </div>
    );
};
