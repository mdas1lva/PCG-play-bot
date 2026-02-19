const ConfigPage = () => {

    const language = useLanguage()

    const configStore = ReactRedux.useSelector(state => state.config);

    const [configState, setConfigState] = React.useState(configStore);
    const [configChanged, setConfigChanged] = React.useState(false);

    React.useEffect(() => {
        setConfigState(configStore)
    }, [configStore])

    React.useEffect(() => {
        setConfigChanged(JSON.stringify(configStore) !== JSON.stringify(configState))
    }, [configState, configStore])

    const handleSave = () => {
        handleSaveConfig(JSON.stringify(configState))
    }

    const handleChangeLanguage = (newValue) => {
        setConfigState(config => {
            return { ...config, language: newValue }
        })
    }

    const handleChangeTheme = (newValue) => {
        setConfigState(config => {
            return { ...config, theme: newValue }
        })
    }

    const handleChangeChannel = (newValue) => {
        setConfigState(config => {
            return { ...config, channel: newValue }
        })
    }

    const handleChangeShopConfig = (newValue) => {
        setConfigState(config => {
            return { ...config, shop: newValue }
        })
    }

    const handleChangeCatchConfig = (newValue) => {
        setConfigState(config => {
            return { ...config, catch: newValue }
        })
    }

    const handleChangeStatsBallConfig = (newValue) => {
        setConfigState(config => {
            return { ...config, stats_balls: newValue }
        })
    }

    const handleChangeDiscordConfig = (newValue) => {
        setConfigState(config => {
            return { ...config, discord: newValue }
        })
    }

    return (
        <div id={"outer-container"} data-theme={configState?.theme || "mocha"}>

            <p id={"page-title"}>{language.PAGE_TITLE}</p>

            <button
                className={`save-button ${configChanged ? "able" : "disabled"}`}
                onClick={handleSave}
                title={language.SAVE_BUTTON}
                disabled={!configChanged}
            >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", fontWeight: "bold", fontSize: "1.2em" }}>
                    SAVE
                </div>
            </button>

            <LanguageAndChannel
                languageConfig={configState.language} setLanguageConfig={handleChangeLanguage}
                themeConfig={configState.theme} setThemeConfig={handleChangeTheme}
                channel={configState.channel} setChannel={handleChangeChannel}
            />

            <Shop
                shopConfig={configState.shop} setShopConfig={handleChangeShopConfig}
            />

            <Capture
                catchConfig={configState.catch} setCatchConfig={handleChangeCatchConfig}
            />

            <StatsBalls
                statsBallsConfig={configState.stats_balls} setStatsBallsConfig={handleChangeStatsBallConfig}
            />

            <Discord
                discordConfig={configState.discord} setDiscordConfig={handleChangeDiscordConfig}
            />

        </div>
    );
};

// ... inside ConfigPage ...

// Helper function
function reformatBallName(name) {
    return name.charAt(0).toUpperCase() + name.slice(1).replace("_", " ");
}


ReactDOM.render(
    <ReactRedux.Provider store={store}>
        <ConfigPage />
    </ReactRedux.Provider>,
    document.getElementById("root")
);
